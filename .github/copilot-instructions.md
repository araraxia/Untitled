# Untitled Instructions
These rules apply to all code in this repository. Follow them exactly unless the user explicitly overrides one.

---

## Project Context
This repository contains a Python project that uses PyWebView to create a desktop application. The project structure includes a backend built with Flask and SocketIO, and a frontend consisting of HTML, CSS, and JavaScript files. The instructions provided here are meant to guide developers in maintaining the code style and structure of the project.

The purpose of this repository branch is to build a modular, flexible and maintainable game engine that can be easily extended with new features and game mechanics. 
The engine is designed with the following ideas in mind:
- Primarily focuses on 2D or 2.5D graphics, but is built with the potential for 3D support in the future.
- Graphics rendering should be handled 
- Code efficient and optimized for performance, especially in the logic and rendering processes. Utilizing hardware acceleration where possible and minimizing unnecessary computations to allow for tracking a large number of entities and complex interactions without significant performance degradation.
- Emphasizes modularity and flexibility, allowing for easy integration of new features and mechanics.

Entry points for the project include:
- `main.py`: The main entry point for the PyWebView application.
- `backend/app.py`: The Flask application that serves the backend API and handles game logic.
- `frontend/index.html`: The main HTML file for the frontend interface.

---

## Code Style Guidelines
1. **Python Code**: Follow PEP 8 style guidelines for Python code. Use 4 spaces for indentation, and limit lines to 79 characters.
2. **JavaScript Code**: Follow the Airbnb JavaScript style guide for JavaScript code. Use 2 spaces for indentation, and use single quotes for strings.
3. **HTML/CSS**: Follow standard HTML5 and CSS3 best practices. Use semantic HTML elements and keep CSS organized and modular.
4. **File Naming**: Use snake_case for Python files and camelCase for JavaScript files. HTML and CSS files should be named descriptively based on their content. Finding existing invalid names should prompt a rename to follow these conventions.
5. **Markdown Table Column Style**: Use the `compact` style for markdown tables as defined in the [GitHub Flavored Markdown Spec](https://github.github.com/gfm/#tables-extension-). This means that there should consistently be a space between the pipe characters and the cell content. For example:
```markdown
| Header 1 | Header 2 |
| -------- | -------- |
| Cell 1   | Cell 2   |
```
6. **Markdown Fenced Code Blocks Should Specify Language**: Always specify the language for fenced code blocks in markdown files to enable syntax highlighting. If no specific language applies, use `text` as the language identifier.

---

## Assets
All assets should be stored in the `frontend/assets/` directory. This includes images, icons, audio files, and any other media used in the project. Assets should be organized into subdirectories based on their type (e.g., `assets/images/`, `assets/icons/`, `assets/audio/`). When adding new assets, ensure that they are optimized for performance and do not unnecessarily increase the size of the project.

## Pip Packages
All Python dependencies should be listed in the `requirements.txt` file. When adding new dependencies, ensure that they are necessary for the project and do not introduce unnecessary bloat. Use specific version numbers to ensure compatibility and reproducibility of the development environment. When installing new packages, use pip and add them to the `requirements.txt` file using the following command:
```cmd
pip install <package_name>==<version> -r requirements.txt
```