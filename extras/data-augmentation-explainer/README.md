# data-augmentation-explainer

A small interactive page, in English and French, that walks through how the dataset was class-balanced: the original class imbalance, targeted Albumentations augmentation of the minority classes, and the on-the-fly augmentation YOLOv8 adds during training. It was made to present the augmentation step and is kept here as supporting material; the app and the training scripts do not depend on it. Its figures come from the original notebook pipeline, which augmented the whole dataset before splitting. `scripts/prepare_dataset.py` now augments the training split only, so its counts differ (see `docs/LIMITATIONS.md`).

## How to run locally

1. Install dependencies
```bash
npm install
```

2. Start the dev server
```bash
npm run dev
```

3. Open the URL shown by Vite (usually http://localhost:5173)

## Notes

- Tailwind is configured via `tailwind.config.js` and `postcss.config.js`.
- Recharts and lucide-react are added as dependencies in `package.json`.
