"""Main entry point for the desktop application.

Thin wrapper around client.main.main() -- Step 15 task 5 of
.github/prompts/wgpu-py-migration.prompt.md. The native wgpu-py/GLFW/
imgui client (client/main.py) replaces this file's former PyWebView
bootstrap (window = webview.create_window(...); webview.start(...)) --
kept as a thin wrapper rather than replaced outright so `run.bat`'s
existing `python main.py` invocation keeps working unchanged (task 6:
"pick whichever keeps run.bat working with the smallest change").

The `should_disable_gpu()` Nouveau workaround and all `webview.*`
calls this file used to contain are gone entirely, not ported --
per task 4, they existed specifically to work around WebKitGTK/
PyWebView issues this migration removes.
"""

from client.main import main

if __name__ == "__main__":
    main()
