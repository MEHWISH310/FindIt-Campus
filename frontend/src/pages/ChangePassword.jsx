import { useNavigate } from 'react-router-dom';
import Modal from '../components/Modal';
import ChangePasswordForm from '../components/ChangePasswordForm';

// Same "Reset password" popup the profile page shows -- rendered as a
// standalone route so the footer / a direct link land on the identical UI
// rather than a differently-styled full page.
export default function ChangePassword() {
  const navigate = useNavigate();
  const close = () => navigate('/me');

  return (
    <Modal onClose={close} labelledBy="pw-modal-heading">
      <h2 id="pw-modal-heading" className="modal-heading">
        Reset password
      </h2>
      <ChangePasswordForm
        bare
        onCancel={close}
        onSuccess={() => setTimeout(close, 900)}
      />
    </Modal>
  );
}
