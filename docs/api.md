# API reference

`curved_text` and `CurvedText` take the same arguments and make the same
artist. The function takes the axes first, as matplotlib's helper functions do.
The class takes it after `x, y, text`, as `matplotlib.text.Text` does. The Notes
and Limits of `CurvedText` say what can change after creation.

```{eval-rst}
.. autofunction:: curved_text.curved_text

.. autoclass:: curved_text.CurvedText
   :members:
   :show-inheritance:
   :exclude-members: set
```
