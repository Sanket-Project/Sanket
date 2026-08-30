import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

interface ProductImagesState {
  images: Record<string, string>; // Maps product ID or SKU ID to user uploaded base64 dataUrls
  uploadImage: (id: string, dataUrl: string) => void;
  removeImage: (id: string) => void;
}

export const useProductImagesStore = create<ProductImagesState>()(
  persist(
    (set) => ({
      images: {},
      uploadImage: (id, dataUrl) =>
        set((state) => ({
          images: { ...state.images, [id]: dataUrl },
        })),
      removeImage: (id) =>
        set((state) => {
          const nextImages = { ...state.images };
          delete nextImages[id];
          return { images: nextImages };
        }),
    }),
    {
      name: "sanket.product-images",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);

// Helper function to resolve the image for a product or SKU
export function getProductImage(
  id: string,
  industry: string,
  userImages: Record<string, string> = useProductImagesStore.getState().images,
  descriptor = "",
): string {
  // 1. If user uploaded a custom image, use it
  if (userImages[id]) {
    return userImages[id];
  }

  // 2. Fashion uses distinct, product-specific catalog photography. Product
  // names, categories, variant descriptions, and SKU codes can all be passed
  // in the descriptor so colour variants resolve to the right asset.
  const lowerInd = (industry ?? "electronics").toLowerCase();
  const product = `${id} ${descriptor}`.toLowerCase().replace(/[-_]/g, " ");
  const asset = (name: string) => `${import.meta.env.BASE_URL}assets/products/${name}`;

  if (lowerInd === "fashion") {
    if (/short/.test(product)) return asset("fashion-shorts-black.png");
    if (/trench|overcoat|coat/.test(product)) return asset("fashion-trench-taupe.png");
    if (/denim|jean/.test(product)) return asset("fashion-jeans-indigo.png");
    if (/sweater|wool|knit/.test(product)) return asset("fashion-sweater-cream.png");
    if (/linen|button down|shirt/.test(product) && !/t\s?shirt|tee/.test(product)) {
      return asset("fashion-shirt-white-linen.png");
    }
    if (/windbreaker|jacket/.test(product)) return asset("fashion-jacket-olive.png");
    if (/sneaker|shoe|footwear/.test(product)) {
      if (/black/.test(product)) return asset("fashion-sneaker-black.png");
      if (/white/.test(product)) return asset("fashion-sneaker-white.png");
      return asset("fashion-sneaker-red-canvas.png");
    }
    if (/t\s?shirt|tee|cotton/.test(product)) {
      if (/red/.test(product)) return asset("fashion-tshirt-red.png");
      if (/white/.test(product)) return asset("fashion-tshirt-white.png");
      return asset("fashion-tshirt-black.png");
    }
    return asset("fashion-trench-taupe.png");
  }

  // 3. Every sandbox industry uses real category-specific catalogue
  // photography. The first match is also the industry fallback, so an
  // unfamiliar product never falls through to an unrelated chip illustration.
  if (lowerInd === "electronics") {
    if (/headphone|headset|anc/.test(product)) return asset("electronics-headphones.webp");
    if (/speaker|bluetooth|audio/.test(product)) return asset("electronics-speaker.webp");
    if (/laptop|ultrabook|notebook/.test(product)) return asset("electronics-laptop.webp");
    if (/watch|wearable|fitness/.test(product)) return asset("electronics-smartwatch.webp");
    return asset("electronics-headphones.webp");
  }

  if (lowerInd === "pharma") {
    if (/ibuprofen|\bibu\b|analgesic|pain/.test(product)) return asset("pharma-ibuprofen.webp");
    if (/amoxicillin|\bamox\b|antibiotic|capsule/.test(product)) return asset("pharma-amoxicillin.webp");
    if (/insulin|injection|glargine/.test(product)) return asset("pharma-insulin-pen.webp");
    if (/vitamin|vitc|supplement|ascorbic/.test(product)) return asset("pharma-vitamin-c.webp");
    return asset("pharma-ibuprofen.webp");
  }

  if (lowerInd === "agrocenter") {
    if (/feed|poultry|pellet/.test(product)) return asset("agro-poultry-feed.webp");
    if (/fertili|\bfert\b|npk|nutrient/.test(product)) return asset("agro-fertilizer.webp");
    if (/pest|insect|herbicide|spray/.test(product)) return asset("agro-pesticide.webp");
    if (/seed|corn|maize/.test(product)) return asset("agro-corn-seed.webp");
    return asset("agro-poultry-feed.webp");
  }

  if (lowerInd === "hardware") {
    if (/cement|concrete|mortar/.test(product)) return asset("hardware-cement.webp");
    if (/wire|cable|electrical/.test(product)) return asset("hardware-wire.webp");
    if (/bolt|nut|washer|fastener|\bfast\b/.test(product)) return asset("hardware-fasteners.webp");
    if (/pipe|pvc|plumb/.test(product)) return asset("hardware-pvc-pipe.webp");
    if (/drill|power tool|hammer/.test(product)) return asset("hardware-drill.webp");
    if (/helmet|ppe|safety/.test(product)) return asset("hardware-safety-helmet.webp");
    return asset("hardware-cement.webp");
  }

  return asset("electronics-headphones.webp");
}
