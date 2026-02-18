# **Python Coding Rules**

## **1. Language & Communication**

* **Strict English Policy:** All code, variable names, function names, class names, comments, docstrings, and commit messages must be in **English**.  
* **Tone:** Professional, technical, and concise.

## **2. Mandatory File Structure & Header**

Every Python file must start with the following standard header:
```python
"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           [Insert Filename]
Version:        [Insert Version Number]
Producer:       thorsten.schnebeck@gmx.net
Generator:      Gemini 3pro
Description:    [Insert concise description]
------------------------------------------------------------------------------
"""
```

## **3. Coding Standards & Syntax**

### **A. Formatting & Style (PEP 8+)**
* **One Command Per Line:** Avoid multiple statements on a single line.
* **Harmonized Naming:**  
  * Classes: PascalCase  
  * Variables/Functions/Methods: snake_case  
  * Constants: UPPER_CASE  
  * Private members: _leading_underscore  
* **Type Hinting: MANDATORY.** Every function signature must include type hints for arguments and return values.

### **B. Modernization**
* **String Formatting:** Use **f-strings** exclusively. (Exception: `tr()` calls, see i18n).
* **Path Handling:** Use **pathlib** instead of os.path where applicable.
* **Collections:** Use literal syntax for lists/dicts (e.g., [], {}) instead of list(), dict().

### **C. No Legacy Code Support**
* **Strict Modernization:** Support for legacy data structures or old code paths within production logic is **forbidden**.
* **Transition Strategy:** If breaking changes occur (e.g., schema migration), implement a separate, isolated conversion script or routine to migrate user data once.
* **Refactoring:** After migration, delete all legacy code immediately. Do not keep "backward compatibility" branches or `if legacy:` blocks in the main logic.

## **4. Documentation Standards**
* **Docstrings:** Every Class, Method, and Function must have a docstring (Google Style preferred).
* **Content:** Describe purpose, Args, Returns, and Raises.

## **5. Logic & Security**
* **DRY Principle:** Refactor duplicate logic into reusable helper functions.
* **Complexity:** Refactor deeply nested code into separate methods.
* **Error Handling:** Catch specific errors (e.g., `except ValueError:`). Never use bare `except:`.
* **Secrets:** Never hardcode secrets. Use environment variables.

## **6. Internationalization (i18n)**
* **Strict tr() Usage:** NEVER use hardcoded strings for user-facing GUI elements. Always wrap them in `self.tr("Your String")`.
* **Dynamic Content:** For strings with variables, use positional placeholders: `self.tr("File %s not found") % filename`.
* **Resource Maintenance:** Run `pylupdate6` to sync `.ts` files after adding/changing strings.
* **Dynamic UI Layouts:** To support localized text, avoid fixed widths for UI elements. Use dynamic padding and `setSizeAdjustPolicy` for widgets (see `agent_framework.md` Section 5.2).