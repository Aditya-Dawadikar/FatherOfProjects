import type { IconType } from 'react-icons'
import { FaGithub, FaLinkedin } from 'react-icons/fa'
import { FiInfo, FiMail, FiMapPin, FiPhone } from 'react-icons/fi'
import { SiLeetcode } from 'react-icons/si'
import profile from '../../data/profile.json'
import { PRODUCT_NAME, PRODUCT_TAGLINE } from '../../lib/brand'
import { trackEvent } from '../../lib/posthog'
import BrandMark from '../BrandMark'

// Landing page footer: the "this is a demo" notice, then the author's contact details and
// profiles. Everything personal comes from src/data/profile.json -- github/leetcode/linkedin are
// full profile URLs; any field left empty is simply not shown.

type ProfileLink = { key: string; label: string; href: string; icon: IconType }

function nonEmpty<T extends { href: string }>(items: T[]) {
  return items.filter((item) => item.href.trim() !== '')
}

export default function LandingFooter() {
  const profileLinks: ProfileLink[] = nonEmpty([
    { key: 'github', label: 'GitHub', href: profile.github, icon: FaGithub },
    { key: 'leetcode', label: 'LeetCode', href: profile.leetcode, icon: SiLeetcode },
    { key: 'linkedin', label: 'LinkedIn', href: profile.linkedin, icon: FaLinkedin },
  ])
  const contactLinks = nonEmpty([
    { key: 'email', label: profile.email, href: profile.email ? `mailto:${profile.email}` : '', icon: FiMail },
    { key: 'phone', label: profile.phone, href: profile.phone ? `tel:${profile.phone.replace(/[^\d+]/g, '')}` : '', icon: FiPhone },
  ])
  const hasProfile = Boolean(profile.name || profileLinks.length || contactLinks.length || profile.location)
  const trackProfileClick = (kind: string) => trackEvent('landing_profile_link_clicked', { kind })

  return (
    <footer className="landing-site-footer">
      <aside className="landing-disclaimer" aria-label="About this demo">
        <FiInfo aria-hidden="true" className="landing-disclaimer-icon" />
        <div>
          <strong>A demo, not a service.</strong>
          <p>
            {PRODUCT_NAME} is a proof of concept, built for recruiters and engineers to look around. It isn't offered as a
            product, and it isn't processing new job postings right now: every score is a paid LLM call, and this project
            has no funding behind it. Everything you see is data the pipeline collected while it was running.
          </p>
        </div>
      </aside>

      <div className="landing-site-footer-grid">
        <div className="landing-site-footer-brand">
          <span className="landing-brand">
            <BrandMark />
            {PRODUCT_NAME}
          </span>
          <span className="landing-site-footer-tagline">{PRODUCT_TAGLINE}</span>
          {profile.name && (
            <span className="landing-site-footer-author">
              Built by <strong>{profile.name}</strong>
              {profile.headline && <> · {profile.headline}</>}
            </span>
          )}
        </div>

        {(contactLinks.length > 0 || profile.location) && (
          <div className="landing-site-footer-column">
            <span className="landing-mono is-upper">Contact</span>
            {contactLinks.map((link) => (
              <a key={link.key} href={link.href} className="landing-site-footer-link" onClick={() => trackProfileClick(link.key)}>
                <link.icon aria-hidden="true" />
                {link.label}
              </a>
            ))}
            {profile.location && (
              <span className="landing-site-footer-link">
                <FiMapPin aria-hidden="true" />
                {profile.location}
              </span>
            )}
          </div>
        )}

        {profileLinks.length > 0 && (
          <div className="landing-site-footer-column">
            <span className="landing-mono is-upper">Profiles</span>
            <div className="landing-site-footer-profiles">
              {profileLinks.map((link) => (
                <a
                  key={link.key}
                  href={link.href}
                  target="_blank"
                  rel="noreferrer"
                  className="landing-profile-button"
                  onClick={() => trackProfileClick(link.key)}
                >
                  <link.icon aria-hidden="true" />
                  {link.label}
                </a>
              ))}
            </div>
          </div>
        )}

        {!hasProfile && import.meta.env.DEV && (
          <div className="landing-site-footer-column">
            <span className="landing-mono is-upper">Dev note</span>
            <span className="landing-site-footer-link">Fill in src/data/profile.json to show contact details and profiles here.</span>
          </div>
        )}
      </div>

      <div className="landing-site-footer-bottom">
        <span>
          © {new Date().getFullYear()} {profile.name || PRODUCT_NAME}
        </span>
        <span className="landing-mono">Python · LangGraph · Gemini · MLflow · Postgres · Redis · React</span>
      </div>
    </footer>
  )
}
