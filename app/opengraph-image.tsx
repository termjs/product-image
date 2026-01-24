import { ImageResponse } from "next/og";

export const runtime = "edge";

export const alt = "Product Image Processor - Standardize your product images";
export const size = {
  width: 1200,
  height: 630,
};

export const contentType = "image/png";

export default async function Image() {
  const geistSemiBold = fetch(
    new URL("./Geist-SemiBold.ttf", import.meta.url),
  ).then((res) => res.arrayBuffer());

  return new ImageResponse(
    <div
      style={{
        height: "100%",
        width: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: "#000",
      }}
    >
      <h1
        style={{
          fontSize: "80px",
          fontWeight: 600,
          color: "#fff",
          textAlign: "center",
          fontFamily: "Geist",
          padding: "0 80px",
        }}
      >
        Product Image Processor
      </h1>
    </div>,
    {
      ...size,
      fonts: [
        {
          name: "Geist",
          data: await geistSemiBold,
          style: "normal",
          weight: 600,
        },
      ],
    },
  );
}
