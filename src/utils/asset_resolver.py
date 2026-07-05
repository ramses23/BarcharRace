import re
from pathlib import Path


class AssetResolver:
    def __init__(self, assets_dir, extensions):
        self.assets_dir = Path(assets_dir)
        self.extensions = tuple(extension.lower() for extension in extensions)
        self.asset_index = self._build_index()

    def resolve(self, name):
        key = self.normalize_name(name)
        path = self.asset_index.get(key)

        return str(path) if path else None

    def _build_index(self):
        if not self.assets_dir.exists():
            return {}

        index = {}

        for asset_path in self.assets_dir.iterdir():
            if not asset_path.is_file():
                continue

            if asset_path.suffix.lower() not in self.extensions:
                continue

            key = self.normalize_name(asset_path.stem)
            index.setdefault(key, asset_path)

        return index

    @staticmethod
    def normalize_name(name):
        normalized = re.sub(r"[^a-z0-9]+", "_", str(name).lower())
        return normalized.strip("_")
