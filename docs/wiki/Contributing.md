# Contributing to MailLogSentinel

We welcome contributions to MailLogSentinel! Whether you're interested in fixing bugs, adding new features, improving documentation, or sharing ideas, your help is appreciated.

## How to Contribute

This project follows a simple contribution workflow:

1.  **Fork the Repository:**
    Start by forking the [MailLogSentinel GitHub repository](https://github.com/monozoide/MailLogSentinel) to your own GitHub account.

2.  **Create a Branch:**
    Create a new branch in your forked repository for your changes. Choose a descriptive branch name (e.g., `feature/add-new-report-format` or `bugfix/resolve-parsing-error`).
    ```bash
    git checkout -b feature/your-new-feature
    ```

3.  **Make Your Changes:**
    Implement your feature, bug fix, or documentation update.
    *   **Code:** If you're writing code, try to follow the existing coding style. Add comments where necessary.
    *   **Documentation:** For documentation changes, ensure clarity and accuracy.
    *   **Tests:** If you're adding a new feature or fixing a bug, consider adding unit tests to cover your changes. (This is an area for future growth in the project).

4.  **Commit Your Changes:**
    Commit your changes with a clear and concise commit message.
    ```bash
    git commit -m "Add feature: Describe your new feature"
    ```
    Or for a bug fix:
    ```bash
    git commit -m "Fix: Describe the bug and your solution"
    ```

5.  **Push to Your Fork:**
    Push your changes to your forked repository on GitHub.
    ```bash
    git push origin feature/your-new-feature
    ```

6.  **Open a Pull Request:**
    Go to the original MailLogSentinel repository on GitHub and open a Pull Request (PR) from your forked branch to the `main` branch of the MailLogSentinel repository.
    *   Provide a clear title and description for your PR, explaining the purpose and nature of your changes.
    *   If your PR addresses an existing issue, reference it in the description (e.g., "Closes #123").

## Coding Guidelines (General)

While there aren't strict, formalized coding guidelines at this stage, please try to:

*   Write clear, readable Python code.
*   Follow PEP 8 conventions where practical.
*   Comment your code, especially complex parts or non-obvious logic.
*   Ensure your changes don't break existing functionality.
*   If adding new dependencies, justify their need.

## Reporting Bugs

If you find a bug, please report it by opening an issue on the [GitHub Issues page](https://github.com/monozoide/MailLogSentinel/issues).

When reporting a bug, please include:

*   **A clear and descriptive title.**
*   **Steps to reproduce the bug:** Be as specific as possible.
*   **What you expected to happen.**
*   **What actually happened:** Include any error messages or logs.
*   **Your environment:**
    *   MailLogSentinel version (e.g., `v1.0.4-B`).
    *   Python version (e.g., `Python 3.9.2`).
    *   Operating System (e.g., `Debian 11`, `Ubuntu 20.04`).
    *   Relevant parts of your `maillogsentinel.conf` (please redact any sensitive information).
*   **Additional context:** Screenshots, log excerpts, etc., can be very helpful.

You can use the "Good First Issue" template from the `README.md` as a basis:
```
🐛 Bug or ✨ Feature Request

**Description**: _Short description of the issue or feature._

**Steps to Reproduce**:
1. ...
2. ...

**Expected Behavior**: _What you expected._

**Environment**:
- MailLogSentinel vX.Y.Z
- Python 3.x
- OS: e.g. Debian 11

**Additional Context**: _Screenshots, logs, etc._
```

## Questions or Need Help?

If you have questions, need assistance with a contribution, or just want to discuss an idea, feel free to:
*   Open an issue on GitHub.
*   Contact the project maintainer (monozoide) through GitHub.

Thank you for considering contributing to MailLogSentinel! Your efforts help make the project better for everyone. ❤️
