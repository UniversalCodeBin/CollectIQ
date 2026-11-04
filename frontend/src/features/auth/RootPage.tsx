import { Navigate } from "react-router";
import { SessionGate } from "../../app/SessionGate";
import { homeFor } from "./routing";

export function RootPage() {
  return <SessionGate>{(session) => <Navigate to={homeFor(session)} replace />}</SessionGate>;
}
