/*
 * pages/NotAllowedPage.jsx - Shown when a user opens another role's page
 */
import { Link } from 'react-router-dom';
import { ShieldX } from 'lucide-react';
import { useAuth } from '@/components/common/AuthContext';

export default function NotAllowedPage() {
  const { user } = useAuth();
  return (
    <div className="empty">
      <ShieldX size={40} />
      <h1>This page is not available for your role</h1>
      <Link className="btn" to={user.home_path}>Go to my home page</Link>
    </div>
  );
}