# computer_vision — the camera on this PC

The camera work is in `../desktop/camera_reader.py`: it lists the connected
cameras, takes a frame, reads the text with Tesseract and sends the frame to
the provider for a description. It needs Windows, Tesseract on the PATH and
the language data for the language that is chosen.

Reading the screen of the PC itself is not implemented here. A screen
capture has to be written for the Windows desktop API, and nothing in this
folder pretends to do it.
See ../docs/ARCHITECTURE.md for the roadmap and permission boundaries.
