# API reference

This application programming interface (API) reference covers a function and
an artist class: `curved_text` and `CurvedText`. They take the same arguments
and make the same artist. Keep the returned object to hide it (`set_visible`),
restack it (`set_zorder`), change its clipping, or remove it (`remove()`). To
change the text, color, size, or curve, remove the label and make a new one.
`get_text()` does not return the label's string.

```{eval-rst}
.. autofunction:: curved_text.curved_text

.. autoclass:: curved_text.CurvedText
   :members:
   :show-inheritance:
   :exclude-members: set
```
