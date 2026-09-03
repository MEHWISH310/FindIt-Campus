import { Link } from 'react-router-dom';
import ChangePasswordForm from '../components/ChangePasswordForm';

export default function ChangePassword() {
  return (
    <div className="report-page">
      <Link to="/me" className="back-link">
        ← Back
      </Link>
      <ChangePasswordForm />
    </div>
  );
}
