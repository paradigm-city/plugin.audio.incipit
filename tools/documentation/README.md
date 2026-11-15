# The integrated documentation's generator

Makes `docs/Incipit_Documentation.docx` from the source code, the concept documents' content (written into
`part1.py` to `part3.py` and `appendix.py`) and figures drawn here. Not part of the add-on.

Needs: Python 3.9+ with `python-docx`, `pymupdf`, `pillow` and `numpy` (a venv of its own); LibreOffice (for the page
numbers of the contents and the index); the sound engine set up, with an analysed library (for the charts of
chapters 3 and 4).

Steps, from this folder:

1. `python extract.py ../.. catalogue.json`: the method catalogue from the syntax tree
2. `python facts.py ../.. facts.json`: metrics, duplicated helpers, fan-in, router actions, settings, tests
3. `<addon_data>/plugin.audio.incipit/soundprint/python/Scripts/python.exe data_figs.py ../.. <addon_data>/plugin.audio.incipit/soundprint figdata.npz`:
   the data behind the signal-processing charts, with the sound engine's own code (read-only)
4. `python diagrams_fix.py fig_context fig_three_steps fig_pipeline fig_snippets fig_filterbank fig_spectrogram fig_cosine fig_similarity fig_variety fig_character fig_ai fig_components fig_runtime fig_service_loop fig_dataflow_mix fig_messaging fig_kodi fig_states fig_modules fig_er fig_review fig_outlook seqs`:
   all figures into `figs/` (`diagrams_fix.py` redraws three of `diagrams.py`'s first versions)
5. `python build.py ../../docs/Incipit_Documentation.docx`: three passes; the second is rendered by LibreOffice to
   find the pages for the contents, the lists of figures and tables, and the index

Word updates the fields (contents, index) when the document is opened.

Hand-written facts (version, commit, dates, measured numbers) are in `build.py` (`INFO`) and in the text of the
`part*.py` files: check them against the code before a new edition.
