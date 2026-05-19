interface PageLoaderProps {
  variant?: 'dark' | 'light';
}

export default function PageLoader(_props: PageLoaderProps) {
  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-[#0a0f1a]">
      <video
        src="/loader.mp4"
        autoPlay
        loop
        muted
        playsInline
        className="h-full w-full object-contain"
        style={{ pointerEvents: 'none' }}
      />
    </div>
  );
}
