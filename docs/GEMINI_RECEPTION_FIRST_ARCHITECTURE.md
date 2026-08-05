# Gemini Reception-First Competition Edition

## Competition entry point

Start `START_GEMINI_RECEPTION_DEMO.bat`. The competition edition opens only the
client-facing reception conversation at `http://127.0.0.1:8770/client`.

The dual-line Tkinter interface is deliberately not shown by this launcher. It
remains an internal lawyer workbench and may be opened separately during the
recording to explain the machinery behind the client experience.

## Real software link

The reception page is not a one-question/one-answer legal chatbot. Its case
organisation and 18-dimension review are routed through
`lawyer_software_bridge.py`, which imports the existing online lawyer core:

- `LLMClient` and its verified provider routes;
- the same `api_profiles.local.json` provider configuration;
- the same 18 dimension definitions and English labels;
- the same structured whole-case weakness prompt;
- the same capacity-splitting behaviour when a full 18-dimension response is
  too large; and
- the same final no-material-weakness display filter.

The bridge runs these functions headlessly. No internal Tkinter window needs to
appear in the customer journey.

## Demonstration sequence

1. Open the reception-first competition window.
2. Enter a fictional matter and let Gemini ask for missing facts and evidence.
3. Generate the complete case-material report.
4. Register or log in and run the 18-dimension weakness review.
5. Request human involvement and show the prepared lawyer dossier.
6. Separately open the unchanged dual-line software during the video only when
   explaining how the internal lawyer workbench uses the same case frames,
   providers, dimensions, weakness cards, and advanced opposition tools.

## Source boundary

This directory is a separate competition copy created on 21 July 2026. The
earlier Pinch competition build and the retained dual-line builds are not edited
by this reception-first version.
