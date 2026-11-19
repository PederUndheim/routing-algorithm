/** The few icons the app uses, inline so there is no icon font to load. */

const Svg = ({ children, size = 20 }: { children: React.ReactNode; size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {children}
  </svg>
);

export const ChevronLeft = () => <Svg size={26}><path d="M15 18l-6-6 6-6" /></Svg>;
export const ChevronRight = () => <Svg size={26}><path d="M9 18l6-6-6-6" /></Svg>;
export const ListIcon = () => <Svg><path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01" /></Svg>;
export const CloseIcon = () => <Svg><path d="M18 6L6 18M6 6l12 12" /></Svg>;
export const KeyboardIcon = () => (
  <Svg>
    <rect x="2" y="5" width="20" height="14" rx="2.5" />
    <path d="M6 9h.01M10 9h.01M14 9h.01M18 9h.01M6 13h.01M18 13h.01M9 15.5h6" />
  </Svg>
);
export const CheckIcon = ({ size = 16 }: { size?: number }) => <Svg size={size}><path d="M20 6L9 17l-5-5" /></Svg>;
export const DoubtIcon = () => (
  <Svg size={18}><circle cx="12" cy="12" r="9.5" /><path d="M9.2 9.2a3 3 0 015.6 1.3c0 2-2.8 2.5-2.8 4M12 17.5h.01" /></Svg>
);
export const FlagIcon = () => <Svg size={18}><path d="M5 21V4m0 0h11l-2 4 2 4H5" /></Svg>;
export const MinusIcon = () => <Svg size={18}><path d="M5 12h14" /></Svg>;
export const PlusIcon = () => <Svg size={18}><path d="M12 5v14M5 12h14" /></Svg>;
/** A route with a new point on it. */
export const MidpointIcon = () => (
  <Svg size={18}><path d="M4 20c3-6 5-8 8-8s5-2 8-8" /><circle cx="12" cy="12" r="2.6" fill="currentColor" /></Svg>
);
/** A map pin: where the tour ends. */
export const EndpointIcon = () => (
  <Svg size={18}><path d="M12 21s-6-5.6-6-11a6 6 0 0 1 12 0c0 5.4-6 11-6 11z" /><circle cx="12" cy="10" r="2" /></Svg>
);
/** One route forking into two. */
export const SplitIcon = () => <Svg size={18}><path d="M12 21v-8M12 13L6 4M12 13l6-9" /></Svg>;
