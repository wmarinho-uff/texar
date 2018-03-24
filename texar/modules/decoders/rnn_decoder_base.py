#
"""
Base class for RNN decoders.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

# pylint: disable=not-context-manager, too-many-arguments, no-name-in-module
# pylint: disable=too-many-branches, protected-access, W0221

import tensorflow as tf
from tensorflow.contrib.seq2seq import Decoder as TFDecoder
from tensorflow.contrib.seq2seq import dynamic_decode
from tensorflow.python.framework import tensor_shape
from tensorflow.python.util import nest

from texar.core import layers
from texar.utils import utils
from texar import context
from texar.module_base import ModuleBase
from texar.modules.decoders import rnn_decoder_helpers

__all__ = [
    "RNNDecoderBase"
]

class RNNDecoderBase(ModuleBase, TFDecoder):
    """Base class inherited by all RNN decoder classes.

    See :class:`~texar.modules.BasicRNNDecoder` for the argumenrts.
    """

    def __init__(self,
                 cell=None,
                 vocab_size=None,
                 output_layer=None,
                 hparams=None):
        ModuleBase.__init__(self, hparams)

        self._helper = None
        self._initial_state = None

        # Make rnn cell
        with tf.variable_scope(self.variable_scope):
            if cell is not None:
                self._cell = cell
            else:
                self._cell = layers.get_rnn_cell(self._hparams.rnn_cell)

        #self._external_cell_given = False
        #if cell is not None:
        #    self._cell = cell
        #    self._external_cell_given = True

        # Make the output layer
        self._vocab_size = vocab_size
        self._output_layer = output_layer
        if output_layer is None:
            if self._vocab_size is None:
                raise ValueError(
                    "Either `output_layer` or `vocab_size` must be provided. "
                    "Set `output_layer=tf.identity` if no output layer is "
                    "wanted.")
            with tf.variable_scope(self.variable_scope):
                self._output_layer = tf.layers.Dense(units=self._vocab_size)
        elif output_layer is not tf.identity:
            if not isinstance(output_layer, tf.layers.Layer):
                raise ValueError(
                    "`output_layer` must be either `tf.identity` or "
                    "an instance of `tf.layers.Layer`.")

    @staticmethod
    def default_hparams():
        """Returns a dictionary of hyperparameters with default values.

        The hyperparameters have the same structure as in
        :meth:`~texar.modules.BasicRNNDecoder.default_hparams` of
        :class:`~texar.modules.BasicRNNDecoder`, except that the default
        "name" here is "rnn_decoder".
        """
        return {
            "rnn_cell": layers.default_rnn_cell_hparams(),
            "helper_train": rnn_decoder_helpers.default_helper_train_hparams(),
            "helper_infer": rnn_decoder_helpers.default_helper_infer_hparams(),
            "max_decoding_length_train": None,
            "max_decoding_length_infer": None,
            "name": "rnn_decoder"
        }

    def _build(self, helper, initial_state=None):
        """Performs decoding.

        Args:
            helper: An instance of `tf.contrib.seq2seq.Helper` that helps with
                the decoding process. For example, use an instance of
                `TrainingHelper` in training phase.
            initial_state (optional): Initial state of decoding.
                If `None` (default), zero state is used.
            mode (optional): A member of
                :tf_main:`tf.estimator.ModeKeys <estimator/ModeKeys>`.
                If `None`, :func:`~texar.context.global_mode` is used.
                Note that if :attr:`cell` is given when constructing the
                deocoder, the :attr:`mode` here does not have an effect to
                :attr:`cell`.

        Returns:
            `(outputs, final_state, sequence_lengths)`: `outputs` is an object
            containing the decoder output on all time steps, `final_state` is
            the cell state of the final time step, `sequence_lengths` is a
            Tensor of shape `[batch_size]`.
        """
        self._helper = helper
        if initial_state is not None:
            self._initial_state = initial_state
        else:
            self._initial_state = self.zero_state(
                batch_size=self.batch_size, dtype=tf.float32)

        max_decoding_length_train = self._hparams.max_decoding_length_train
        if max_decoding_length_train is None:
            max_decoding_length_train = utils.MAX_SEQ_LENGTH
        max_decoding_length_infer = self._hparams.max_decoding_length_infer
        if max_decoding_length_infer is None:
            max_decoding_length_infer = utils.MAX_SEQ_LENGTH
        max_decoding_length = tf.cond(
            #utils.is_train_mode(mode),
            context.global_mode_train(),
            lambda: max_decoding_length_train,
            lambda: max_decoding_length_infer)
        outputs, final_state, sequence_lengths = dynamic_decode(
            decoder=self, maximum_iterations=max_decoding_length)

        if not self._built:
            self._add_internal_trainable_variables()
            # Add trainable variables of `self._cell` which may be
            # constructed externally.
            self._add_trainable_variable(
                layers.get_rnn_cell_trainable_variables(self._cell))
            if isinstance(self._output_layer, tf.layers.Layer):
                self._add_trainable_variable(
                    self._output_layer.trainable_variables)
            self._built = True

        return outputs, final_state, sequence_lengths

    def _rnn_output_size(self):
        size = self._cell.output_size
        if self._output_layer is tf.identity:
            return size
        else:
            # To use layer's compute_output_shape, we need to convert the
            # RNNCell's output_size entries into shapes with an unknown
            # batch size.  We then pass this through the layer's
            # compute_output_shape and read off all but the first (batch)
            # dimensions to get the output size of the rnn with the layer
            # applied to the top.
            output_shape_with_unknown_batch = nest.map_structure(
                lambda s: tensor_shape.TensorShape([None]).concatenate(s),
                size)
            layer_output_shape = self._output_layer.compute_output_shape(
                output_shape_with_unknown_batch)
            return nest.map_structure(lambda s: s[1:], layer_output_shape)

    @property
    def batch_size(self):
        return self._helper.batch_size

    @property
    def output_size(self):
        """Output size of one step.
        """
        raise NotImplementedError

    @property
    def output_dtype(self):
        """Types of output of one step.
        """
        raise NotImplementedError

    def initialize(self, name=None):
        # Inherits from TFDecoder
        # All RNN decoder classes must implement this
        raise NotImplementedError

    def step(self, time, inputs, state, name=None):
        # Inherits from TFDecoder
        # All RNN decoder classes must implement this
        raise NotImplementedError

    def finalize(self, outputs, final_state, sequence_lengths):
        # Inherits from TFDecoder
        # All RNN decoder classes must implement this
        raise NotImplementedError

    @property
    def cell(self):
        """The RNN cell.
        """
        return self._cell

    def zero_state(self, batch_size, dtype):
        """Zero state of the rnn cell.

        Same as :attr:`decoder.cell.zero_state`.
        """
        return self._cell.zero_state(
            batch_size=batch_size, dtype=dtype)

    @property
    def state_size(self):
        """The state size of decoder cell.

        Same as :attr:`decoder.cell.state_size`.
        """
        return self.cell.state_size

    @property
    def vocab_size(self):
        """The vocab size.
        """
        return self._vocab_size
