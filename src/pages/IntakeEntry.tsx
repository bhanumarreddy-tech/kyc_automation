import { Navigate, useParams } from "react-router-dom";

/** Short link target: forwards to the main KYC workflow with the intake token in the query string. */
const IntakeEntry = () => {
  const { token } = useParams();
  const raw = (token ?? "").trim();
  if (!raw) {
    return <Navigate to="/kyc" replace />;
  }
  return <Navigate to={`/kyc?intakeToken=${encodeURIComponent(raw)}`} replace />;
};

export default IntakeEntry;
