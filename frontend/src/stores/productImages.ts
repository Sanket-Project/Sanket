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
): string {
  // 1. If user uploaded a custom image, use it
  if (userImages[id]) {
    return userImages[id];
  }

  // 2. Otherwise, fall back to the beautiful 3D vertical illustrations
  const lowerInd = (industry ?? "electronics").toLowerCase();
  if (lowerInd === "fashion") return "/assets/3d_fashion.png";
  if (lowerInd === "pharma") return "/assets/3d_pharma.png";
  return "/assets/3d_electronics.png";
}
