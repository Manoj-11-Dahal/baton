import type { CSSProperties } from 'react';

/**
 * Agi Super Harness icon set.
 * SVGs live in assets/icons/*.svg (24×24 grid, 1.75 stroke, round caps, currentColor)
 * and are inlined at build time via Vite's import.meta.glob.
 */
const sources = (import.meta as any).glob('../../../assets/icons/*.svg', { query: '?raw', import: 'default', eager: true } as any);

const bodies: Record<string, string> = {};
for (const [file, svg] of Object.entries(sources)) {
  const name = file.slice(file.lastIndexOf('/') + 1, -'.svg'.length);
  bodies[name] = (svg as string).replace(/^\s*<svg[^>]*>/, '').replace(/<\/svg>\s*$/, '');
}

export const iconNames: string[] = Object.keys(bodies).sort();

export function hasIcon(name: string): boolean {
  return Object.prototype.hasOwnProperty.call(bodies, name);
}

export interface IconProps {
  name: string;
  size?: number;
  strokeWidth?: number;
  className?: string;
  style?: CSSProperties;
  title?: string;
}

export function Icon({ name, size = 16, strokeWidth = 1.75, className, style, title }: IconProps) {
  const body = bodies[name];
  return (
    <svg
      className={className ? `icon ${className}` : 'icon'}
      style={style}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
      dangerouslySetInnerHTML={{ __html: body ?? '' }}
    />
  );
}
