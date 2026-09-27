// /social/following route — full-page wrapper around the FollowingPanel.
import { useNavigate } from "react-router-dom";
import { FollowingPanel } from "./FollowingPanel";

export default function SocialFollowingRoute() {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen text-white"
         style={{ background: "linear-gradient(180deg,#080a16 0%,#0b0f1e 40%,#0a0a14 100%)" }}>
      <FollowingPanel onClose={() => navigate("/social")} />
    </div>
  );
}
