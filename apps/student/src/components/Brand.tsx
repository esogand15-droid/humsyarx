import { Icon } from '../icons/Icon';

export type BrandSize = 'sm' | 'md' | 'lg';

const PX: Record<BrandSize, number> = { sm: 28, md: 40, lg: 56 };
const R: Record<BrandSize, number> = { sm: 9, md: 12, lg: 16 };

/** نشان برند — برش واقعی لوگو (کتاب + عصا) روی سرمه‌ای. */
export function Brand({ size = 'md' }: { size?: BrandSize }) {
  return (
    <div
      className="mark mark--brand"
      style={{ width: PX[size], height: PX[size], borderRadius: R[size] }}
      role="img"
      aria-label="هامزیار"
    >
      <span hidden>
        <Icon name="logo-mark" />
      </span>
    </div>
  );
}
