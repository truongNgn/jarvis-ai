"""Confirmed project aliases only; no automatic conversational memory."""


class Preferences:
    def __init__(self):
        self.projects = {"jarvis-ai": "jarvis-ai"}

    def resolve(self, selection):
        # Selection is a trusted client field, never extracted from external text.
        return self.projects.get(selection)

    def choices(self):
        return sorted(self.projects)
