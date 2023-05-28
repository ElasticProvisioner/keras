from keras_core import backend
from keras_core import initializers
from keras_core.api_export import keras_core_export
from keras_core.utils.naming import auto_name
from keras_core.utils.tracking import Tracker


@keras_core_export(["keras_core.Metric", "keras_core.metrics.Metric"])
class Metric:
    """Encapsulates metric logic and state.

    Args:
        name: (Optional) string name of the metric instance.
        dtype: (Optional) data type of the metric result.

    Standalone usage:

    ```python
    m = SomeMetric(...)
    for input in ...:
        m.update_state(input)
    print('Final result: ', m.result())
    ```

    Usage with `compile()` API:

    ```python
    model = keras_core.Sequential()
    model.add(keras_core.layers.Dense(64, activation='relu'))
    model.add(keras_core.layers.Dense(64, activation='relu'))
    model.add(keras_core.layers.Dense(10, activation='softmax'))

    model.compile(optimizer=keras_core.optimizers.RMSprop(0.01),
                  loss=keras_core.losses.CategoricalCrossentropy(),
                  metrics=[keras_core.metrics.CategoricalAccuracy()])

    data = np.random.random((1000, 32))
    labels = np.random.random((1000, 10))

    model.fit(data, labels, epochs=10)
    ```

    To be implemented by subclasses:

    * `__init__()`: All state variables should be created in this method by
      calling `self.add_variable()` like: `self.var = self.add_variable(...)`
    * `update_state()`: Has all updates to the state variables like:
      `self.var.assign(...)`.
    * `result()`: Computes and returns a scalar value or a dict of scalar values
      for the metric from the state variables.

    Example subclass implementation:

    ```python
    class BinaryTruePositives(Metric):

        def __init__(self, name='binary_true_positives', **kwargs):
            super().__init__(name=name, **kwargs)
            self.true_positives = self.add_variable(
                shape=(),
                initializer='zeros',
                name='true_positives'
            )

        def update_state(self, y_true, y_pred, sample_weight=None):
            y_true = ops.cast(y_true, "bool")
            y_pred = ops.cast(y_pred, "bool")

            values = ops.logical_and(
                ops.equal(y_true, True), ops.equal(y_pred, True))
            values = ops.cast(values, self.dtype)
            if sample_weight is not None:
                sample_weight = ops.cast(sample_weight, self.dtype)
                sample_weight = ops.broadcast_to(sample_weight, values.shape)
                values = ops.multiply(values, sample_weight)
            self.true_positives.assign(self.true_positives + ops.sum(values))

        def result(self):
            return self.true_positives
    ```
    """

    def __init__(self, dtype=None, name=None):
        self.name = name or auto_name(self.__class__.__name__)
        self._dtype = dtype
        self._metrics = []
        self._variables = []
        self._tracker = Tracker(
            {
                "variables": (
                    lambda x: isinstance(x, backend.Variable),
                    self._variables,
                ),
                "metrics": (lambda x: isinstance(x, Metric), self._metrics),
            }
        )

    def reset_state(self):
        """Reset all of the metric state variables.

        This function is called between epochs/steps,
        when a metric is evaluated during training.
        """
        for v in self.variables:
            v.assign(0)

    def update_state(self, *args, **kwargs):
        """Accumulate statistics for the metric."""
        raise NotImplementedError

    def result(self):
        """Compute the current metric value.

        Returns:
            A scalar tensor, or a dictionary of scalar tensors.
        """
        raise NotImplementedError

    @property
    def dtype(self):
        return self._dtype

    def add_variable(self, shape, initializer, dtype=None, name=None):
        self._check_super_called()
        initializer = initializers.get(initializer)
        variable = backend.Variable(
            initializer=initializer,
            shape=shape,
            dtype=dtype,
            trainable=False,
            name=name,
        )
        self._variables.append(variable)
        # Prevent double-tracking
        self._tracker.stored_ids["variables"].add(id(variable))
        return variable

    def add_weight(self, *args, **kwargs):
        # Backwards compatibility alias
        return self.add_variable(*args, **kwargs)

    @property
    def variables(self):
        variables = self._variables[:]
        for metric in self._metrics:
            variables.extend(metric._variables)
        return variables

    def __call__(self, *args, **kwargs):
        self._check_super_called()
        self.update_state(*args, **kwargs)
        return self.result()

    def get_config(self):
        """Return the serializable config of the metric."""
        return {"name": self.name, "dtype": self.dtype}

    @classmethod
    def from_config(cls, config):
        return cls(**config)

    def __setattr__(self, name, value):
        # Track Variables, Layers, Metrics
        if hasattr(self, "_tracker"):
            value = self._tracker.track(value)
        return super().__setattr__(name, value)

    def _check_super_called(self):
        if not hasattr(self, "_tracker"):
            raise RuntimeError(
                "You forgot to call `super().__init__()` "
                "in the `__init__()` method. Go add it!"
            )