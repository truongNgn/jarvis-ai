"""Text rendering for task events without exposing credentials or tool bodies."""


def display(item):
    kind = item.get("type", item.get("event", "progress"))
    if item.get("tool"):
        return f"{item['tool']}: {item.get('status', kind)}"
    return str(kind)
