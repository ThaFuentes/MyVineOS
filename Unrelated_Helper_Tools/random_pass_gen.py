# random_password_generator.py
# Full path: (drop this anywhere in your helper tools folder)
# File name: random_password_generator.py
# Brief, detailed purpose: Standalone PyQt6 GUI tool for generating strong random passwords.
# Features:
#   - Adjustable length (8–64)
#   - Checkboxes for lowercase, uppercase, digits, symbols (all enabled by default)
#   - Optional "Avoid ambiguous characters" (removes 0,O,1,l,I to prevent confusion)
#   - Guarantees at least one character from each selected category
#   - Password is hidden by default (toggle to show)
#   - One-click copy to clipboard
# Requirements: pip install pyqt6 pyperclip

import sys
import random
import string
import pyperclip
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSpinBox, QCheckBox, QPushButton,
    QLineEdit, QMessageBox
)
from PyQt6.QtCore import Qt


class PasswordGenerator(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Random Password Generator")
        self.setMinimumWidth(400)

        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # ----- Password Length -----
        length_layout = QHBoxLayout()
        length_label = QLabel("Password Length:")
        self.length_spin = QSpinBox()
        self.length_spin.setRange(8, 64)
        self.length_spin.setValue(20)
        length_layout.addWidget(length_label)
        length_layout.addWidget(self.length_spin)
        main_layout.addLayout(length_layout)

        # ----- Character Type Checkboxes -----
        self.lower_check = QCheckBox("Include lowercase letters (a-z)")
        self.lower_check.setChecked(True)
        main_layout.addWidget(self.lower_check)

        self.upper_check = QCheckBox("Include uppercase letters (A-Z)")
        self.upper_check.setChecked(True)
        main_layout.addWidget(self.upper_check)

        self.digits_check = QCheckBox("Include digits (0-9)")
        self.digits_check.setChecked(True)
        main_layout.addWidget(self.digits_check)

        self.symbols_check = QCheckBox("Include symbols (!@#$%^&* etc.)")
        self.symbols_check.setChecked(True)
        main_layout.addWidget(self.symbols_check)

        self.ambiguous_check = QCheckBox("Avoid ambiguous characters (0, O, 1, l, I)")
        self.ambiguous_check.setChecked(True)  # Recommended default
        main_layout.addWidget(self.ambiguous_check)

        # ----- Generate Button -----
        self.generate_btn = QPushButton("Generate Password")
        self.generate_btn.clicked.connect(self.generate_password)
        main_layout.addWidget(self.generate_btn)

        # ----- Password Display -----
        pass_layout = QHBoxLayout()
        self.password_edit = QLineEdit()
        self.password_edit.setReadOnly(True)
        self.password_edit.setPlaceholderText("Generated password will appear here")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)  # Hidden by default
        pass_layout.addWidget(self.password_edit)

        self.copy_btn = QPushButton("Copy")
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        self.copy_btn.setEnabled(False)
        pass_layout.addWidget(self.copy_btn)

        main_layout.addLayout(pass_layout)

        # ----- Show/Hide Toggle -----
        self.show_check = QCheckBox("Show password")
        self.show_check.stateChanged.connect(self.toggle_visibility)
        main_layout.addWidget(self.show_check)

        self.setLayout(main_layout)

    def generate_password(self):
        length = self.length_spin.value()

        categories = []
        if self.lower_check.isChecked():
            categories.append(string.ascii_lowercase)
        if self.upper_check.isChecked():
            categories.append(string.ascii_uppercase)
        if self.digits_check.isChecked():
            categories.append(string.digits)
        if self.symbols_check.isChecked():
            categories.append(string.punctuation)

        if not categories:
            QMessageBox.warning(self, "Error", "You must select at least one character type!")
            return

        if length < len(categories):
            QMessageBox.warning(
                self,
                "Error",
                f"Password length must be at least {len(categories)} "
                f"to guarantee one character from each selected type."
            )
            return

        # Build pool of allowed characters
        all_chars = ''.join(categories)

        # Remove ambiguous characters if requested
        if self.ambiguous_check.isChecked():
            ambiguous = '0O1lI'
            all_chars = ''.join(c for c in all_chars if c not in ambiguous)

        # Ensure at least one from each category
        password = [random.choice(cat) for cat in categories]

        # Fill the remaining length from the full pool
        remaining = length - len(categories)
        password.extend(random.choice(all_chars) for _ in range(remaining))

        # Shuffle for randomness
        random.shuffle(password)

        generated = ''.join(password)
        self.password_edit.setText(generated)
        self.copy_btn.setEnabled(True)

    def toggle_visibility(self, state):
        if state == Qt.CheckState.Checked.value:
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)

    def copy_to_clipboard(self):
        pyperclip.copy(self.password_edit.text())
        QMessageBox.information(self, "Copied!", "Password copied to clipboard.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PasswordGenerator()
    window.show()
    sys.exit(app.exec())