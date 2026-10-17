import { Menu, ShieldAlert } from 'lucide-react';
import { formatDateTime } from '../utils';

type HeaderProps = {
  onMenu: () => void;
  lastUpdated: string | null;
  apiReady: boolean | null;
};

export function Header({ onMenu, lastUpdated, apiReady }: HeaderProps) {
  return (
    <header className="topbar">
      <button className="mobile-menu" type="button" onClick={onMenu} aria-label="Open navigation">
        <Menu size={20} aria-hidden="true" />
      </button>
      <div className="topbar-title-wrap">
        <div className="eyebrow">AarogyaTwin-X / longitudinal glucose research</div>
        <h1>Patient twin workspace</h1>
      </div>
      <div className="topbar-meta">
        <div className="synthetic-stamp">
          <ShieldAlert size={15} aria-hidden="true" />
          <span>SYNTHETIC RESEARCH</span>
          <strong>Not for clinical use</strong>
        </div>
        <div className={`api-status ${apiReady === false ? 'is-error' : ''}`} role="status" aria-live="polite">
          <span className="status-dot" aria-hidden="true" />
          {apiReady === true ? 'API ready' : apiReady === false ? 'API unavailable' : 'Connecting'}
        </div>
        {lastUpdated && <div className="last-updated">Updated {formatDateTime(lastUpdated)}</div>}
      </div>
    </header>
  );
}
