"""Keep exported review pages usable offline with the local application's styling."""
from pathlib import Path


def embedded_interface_style():
    css = Path(__file__).with_name('templates').joinpath('interface.css').read_text(encoding='utf-8')
    return '<style>' + css + '</style>'
