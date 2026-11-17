export type CropPosition = { x: number; y: number; zoom: number };

export function cropRegion(width: number, height: number, crop: CropPosition) {
  const side = Math.min(width, height) / crop.zoom;
  return { x: crop.x * (width - side), y: crop.y * (height - side), side };
}

export async function cropPhoto(image: HTMLImageElement, crop: CropPosition): Promise<File> {
  const { x, y, side } = cropRegion(image.naturalWidth, image.naturalHeight, crop);
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = Math.max(1, Math.min(768, Math.floor(side)));
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Canvas unavailable");
  context.fillStyle = "#24212f";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(image, x, y, side, side, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob(value => value ? resolve(value) : reject(new Error("Crop failed")), "image/jpeg", 0.92);
  });
  return new File([blob], "profile.jpg", { type: "image/jpeg" });
}
