class ColorPalette:
    def __init__(self, colors):
        if not colors:
            raise ValueError("ColorPalette requires at least one color.")

        self.colors = tuple(colors)
        self.assignments = {}

    def get(self, key):
        if key not in self.assignments:
            color_index = len(self.assignments) % len(self.colors)
            self.assignments[key] = self.colors[color_index]

        return self.assignments[key]
