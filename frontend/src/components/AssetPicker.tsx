import type { Asset } from "../types";

export function AssetPicker({
  assets,
  selectedAssetId,
  onSelect,
}: {
  assets: Asset[];
  selectedAssetId: string | null;
  onSelect: (assetId: string) => void;
}) {
  return (
    <div className="asset-picker">
      <label htmlFor="asset-select">Actif suivi</label>
      <select
        id="asset-select"
        value={selectedAssetId ?? ""}
        onChange={(event) => onSelect(event.target.value)}
        disabled={assets.length === 0}
      >
        {assets.length === 0 && <option value="">Aucun actif</option>}
        {assets.map((asset) => (
          <option key={asset.id} value={asset.id}>
            {asset.symbol} — {asset.name}
          </option>
        ))}
      </select>
    </div>
  );
}
