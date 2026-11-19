import { useTitle } from '../../App';

export default function NoPages() {
  useTitle('Welcome');
  return (
    <div className="tile none">
      <strong>No pages to show yet.</strong>
      <span>Your farm owner hasn't given you access to any page. Ask them to update your permissions.</span>
    </div>
  );
}
