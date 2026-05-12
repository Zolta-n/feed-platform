"""Flask-WTF form definitions for the Niche web tier."""
from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired, Length


class RequestLoginForm(FlaskForm):
    """Magic link request form."""
    email = StringField(
        "Email",
        validators=[DataRequired(), Length(max=254)],
    )
