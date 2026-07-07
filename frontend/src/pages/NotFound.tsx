import { Link } from "react-router-dom";

export const NotFoundPage = () => (
  <div
    style={{
      minHeight: "100vh",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      gap: 24,
      textAlign: "center",
      padding: 32,
      background: "linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)",
    }}
  >
    <div
      style={{
        fontSize: 80,
        fontWeight: 900,
        background: "linear-gradient(135deg, #7c3aed, #a855f7, #6366f1)",
        WebkitBackgroundClip: "text",
        WebkitTextFillColor: "transparent",
        lineHeight: 1,
      }}
    >
      404
    </div>
    <div>
      <h1 style={{ fontSize: 22, fontWeight: 700, color: "#1e293b", marginBottom: 8 }}>
        Page not found
      </h1>
      <p style={{ fontSize: 14, color: "#64748b", maxWidth: 360 }}>
        The page you're looking for doesn't exist or has been moved.
      </p>
    </div>
    <div style={{ display: "flex", gap: 12 }}>
      <Link
        to="/"
        style={{
          padding: "10px 24px",
          borderRadius: 10,
          background: "linear-gradient(135deg, #7c3aed, #6366f1)",
          color: "white",
          fontWeight: 600,
          fontSize: 14,
          textDecoration: "none",
          boxShadow: "0 4px 14px rgba(124,58,237,0.3)",
        }}
      >
        Go home
      </Link>
      <Link
        to="/workspace"
        style={{
          padding: "10px 24px",
          borderRadius: 10,
          border: "1px solid #e2e8f0",
          background: "white",
          color: "#475569",
          fontWeight: 600,
          fontSize: 14,
          textDecoration: "none",
        }}
      >
        Dashboard
      </Link>
    </div>
  </div>
);
