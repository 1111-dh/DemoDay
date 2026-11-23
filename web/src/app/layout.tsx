import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "DemoDay · 영상 스튜디오",
  description: "프로젝트 화면으로 만드는 발표 영상",
};
export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
