import { Activity, BarChart3, FlaskConical, ShieldCheck, Waypoints } from 'lucide-react';

type SidebarProps = {
  mobileOpen: boolean;
  onClose: () => void;
};

const navItems = [
  { href: '#overview', label: 'Twin overview', icon: Activity },
  { href: '#forecast', label: 'Forecast', icon: Waypoints },
  { href: '#sandbox', label: 'Scenario sandbox', icon: FlaskConical },
  { href: '#evaluation', label: 'Evaluation', icon: BarChart3 },
];

export function Sidebar({ mobileOpen, onClose }: SidebarProps) {
  return (
    <>
      <div className={`sidebar-backdrop ${mobileOpen ? 'is-visible' : ''}`} onClick={onClose} />
      <aside className={`sidebar ${mobileOpen ? 'is-open' : ''}`} aria-label="Primary navigation">
        <div className="sidebar-brand">
          <div className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <div>
            <div className="brand-name">AarogyaTwin-X</div>
            <div className="brand-subtitle">Clinical research lab</div>
          </div>
          <button className="sidebar-close" type="button" onClick={onClose} aria-label="Close navigation">
            ×
          </button>
        </div>

        <div className="sidebar-section-label">Workspace</div>
        <nav className="sidebar-nav">
          {navItems.map(({ href, label, icon: Icon }) => (
            <a key={href} href={href} onClick={onClose}>
              <Icon size={17} strokeWidth={1.8} aria-hidden="true" />
              <span>{label}</span>
            </a>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-footnote">
            <ShieldCheck size={16} aria-hidden="true" />
            <span>Local-only synthetic workspace</span>
          </div>
          <div className="sidebar-version">Research build · Day 1 baseline</div>
        </div>
      </aside>
    </>
  );
}
