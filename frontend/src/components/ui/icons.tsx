/**
 * The application's icon vocabulary — the single import site for every glyph
 * in the UI.
 *
 * Iconly supplies the generic interface vocabulary: navigation, actions,
 * identity, time, media, commerce. Its free set is 101 icons and stops at the
 * edge of our domain, so lucide still carries the supply-chain and status
 * glyphs — pills, pallets, trucks, the severity ladder — that Iconly has no
 * equivalent for. The severity family in particular stays whole on lucide:
 * Info, AlertTriangle and AlertOctagon are read against each other in alert
 * lists, and changing sets partway up that ladder reads as a bug.
 *
 * Call sites import from here rather than from lucide-react or react-iconly,
 * so which set backs a given name stays one decision in one file.
 */
import type { ComponentType, SVGProps } from "react";
import type { IconProps as IconlyProps } from "react-iconly";
import IconlyActivity from "react-iconly/dist/Icons/Activity.mjs";
import IconlyAddUser from "react-iconly/dist/Icons/AddUser.mjs";
import IconlyArrowLeft from "react-iconly/dist/Icons/ArrowLeft.mjs";
import IconlyArrowRight from "react-iconly/dist/Icons/ArrowRight.mjs";
import IconlyBag from "react-iconly/dist/Icons/Bag.mjs";
import IconlyBuy from "react-iconly/dist/Icons/Buy.mjs";
import IconlyCalendar from "react-iconly/dist/Icons/Calendar.mjs";
import IconlyCamera from "react-iconly/dist/Icons/Camera.mjs";
import IconlyCategory from "react-iconly/dist/Icons/Category.mjs";
import IconlyChart from "react-iconly/dist/Icons/Chart.mjs";
import IconlyChat from "react-iconly/dist/Icons/Chat.mjs";
import IconlyChevronDown from "react-iconly/dist/Icons/ChevronDown.mjs";
import IconlyChevronLeft from "react-iconly/dist/Icons/ChevronLeft.mjs";
import IconlyChevronRight from "react-iconly/dist/Icons/ChevronRight.mjs";
import IconlyChevronUp from "react-iconly/dist/Icons/ChevronUp.mjs";
import IconlyDelete from "react-iconly/dist/Icons/Delete.mjs";
import IconlyDocument from "react-iconly/dist/Icons/Document.mjs";
import IconlyDownload from "react-iconly/dist/Icons/Download.mjs";
import IconlyFilter from "react-iconly/dist/Icons/Filter.mjs";
import IconlyFilter2 from "react-iconly/dist/Icons/Filter2.mjs";
import IconlyHeart from "react-iconly/dist/Icons/Heart.mjs";
import IconlyHide from "react-iconly/dist/Icons/Hide.mjs";
import IconlyImage from "react-iconly/dist/Icons/Image.mjs";
import IconlyLocation from "react-iconly/dist/Icons/Location.mjs";
import IconlyLock from "react-iconly/dist/Icons/Lock.mjs";
import IconlyLogout from "react-iconly/dist/Icons/Logout.mjs";
import IconlyMessage from "react-iconly/dist/Icons/Message.mjs";
import IconlyNotification from "react-iconly/dist/Icons/Notification.mjs";
import IconlyPlay from "react-iconly/dist/Icons/Play.mjs";
import IconlyPlus from "react-iconly/dist/Icons/Plus.mjs";
import IconlyScan from "react-iconly/dist/Icons/Scan.mjs";
import IconlySearch from "react-iconly/dist/Icons/Search.mjs";
import IconlySend from "react-iconly/dist/Icons/Send.mjs";
import IconlySetting from "react-iconly/dist/Icons/Setting.mjs";
import IconlyShieldDone from "react-iconly/dist/Icons/ShieldDone.mjs";
import IconlyShow from "react-iconly/dist/Icons/Show.mjs";
import IconlyStar from "react-iconly/dist/Icons/Star.mjs";
import IconlyTimeCircle from "react-iconly/dist/Icons/TimeCircle.mjs";
import IconlyTimeSquare from "react-iconly/dist/Icons/TimeSquare.mjs";
import IconlyTwoUsers from "react-iconly/dist/Icons/TwoUsers.mjs";
import IconlyUpload from "react-iconly/dist/Icons/Upload.mjs";
import IconlyUser from "react-iconly/dist/Icons/User.mjs";
import IconlyWallet from "react-iconly/dist/Icons/Wallet.mjs";
import IconlyWork from "react-iconly/dist/Icons/Work.mjs";

/** The props every icon accepts — lucide's calling convention, which the app already speaks. */
export type IconProps = Omit<SVGProps<SVGSVGElement>, "ref"> & {
  size?: number | string;
  strokeWidth?: number | string;
};

/**
 * A component usable anywhere the app stores an icon in data — nav tables,
 * severity maps, the connector catalog. Replaces `LucideIcon`, which can no
 * longer describe the whole set now that some glyphs come from Iconly.
 */
export type AppIcon = ComponentType<IconProps>;

/**
 * Iconly's stroke language, chosen by eye against lucide at the ~16-18px the
 * app actually draws icons at. Iconly's geometry is rounder and more compact
 * than lucide's, so matching lucide's 2px stroke numerically (Iconly's "bold")
 * comes out visibly heavier; 1.5px reads as the same weight.
 */
const ICONLY_SET = "light" as const;
const ICONLY_STROKE = "regular" as const;

const toPixels = (size: IconProps["size"]): number | undefined => {
  if (size === undefined) return undefined;
  const px = typeof size === "number" ? size : Number.parseFloat(size);
  return Number.isFinite(px) ? Math.round(px) : undefined;
};

/**
 * Wrap an Iconly glyph in lucide's calling convention.
 *
 * Three mismatches to absorb. Iconly wants an integer pixel size where lucide
 * takes either a number or a CSS-sized className. It describes stroke weight
 * with keywords rather than a number, so a numeric strokeWidth is accepted and
 * dropped — a call site asking for a hairline gets the house weight instead of
 * a type error. And it derives the SVG role from its own `label` prop, so
 * aria-label is forwarded there; passing it straight through as an attribute
 * would leave a labelled icon still marked role="presentation".
 */
const fromIconly = (
  Glyph: ComponentType<IconlyProps>,
  displayName: string,
): AppIcon => {
  const Icon = ({
    size,
    strokeWidth: _strokeWidth,
    "aria-label": ariaLabel,
    ...rest
  }: IconProps) => {
    const px = toPixels(size);
    return (
      <Glyph
        set={ICONLY_SET}
        stroke={ICONLY_STROKE}
        label={typeof ariaLabel === "string" ? ariaLabel : undefined}
        {...(px === undefined ? {} : { size: px })}
        {...(rest as IconlyProps)}
      />
    );
  };
  Icon.displayName = displayName;
  return Icon;
};

/* ---------------------------------------------------------------- Iconly -- */

/* Navigation and disclosure */
export const ChevronDown = fromIconly(IconlyChevronDown, "ChevronDown");
export const ChevronUp = fromIconly(IconlyChevronUp, "ChevronUp");
export const ChevronLeft = fromIconly(IconlyChevronLeft, "ChevronLeft");
export const ChevronRight = fromIconly(IconlyChevronRight, "ChevronRight");
export const ArrowLeft = fromIconly(IconlyArrowLeft, "ArrowLeft");
export const ArrowRight = fromIconly(IconlyArrowRight, "ArrowRight");
export const LayoutDashboard = fromIconly(IconlyCategory, "LayoutDashboard");
export const LayoutGrid = fromIconly(IconlyCategory, "LayoutGrid");
export const Search = fromIconly(IconlySearch, "Search");

/* Identity and account */
export const User = fromIconly(IconlyUser, "User");
export const UserPlus = fromIconly(IconlyAddUser, "UserPlus");
export const Users = fromIconly(IconlyTwoUsers, "Users");
export const LogOut = fromIconly(IconlyLogout, "LogOut");
export const Briefcase = fromIconly(IconlyWork, "Briefcase");
export const Settings = fromIconly(IconlySetting, "Settings");

/* Access and trust */
export const Lock = fromIconly(IconlyLock, "Lock");
export const Eye = fromIconly(IconlyShow, "Eye");
export const EyeOff = fromIconly(IconlyHide, "EyeOff");
export const Shield = fromIconly(IconlyShieldDone, "Shield");
export const ShieldCheck = fromIconly(IconlyShieldDone, "ShieldCheck");

/* Communication */
export const Bell = fromIconly(IconlyNotification, "Bell");
export const Mail = fromIconly(IconlyMessage, "Mail");
export const MessageCircle = fromIconly(IconlyChat, "MessageCircle");
export const MessageSquare = fromIconly(IconlyChat, "MessageSquare");
export const Send = fromIconly(IconlySend, "Send");

/* Time */
export const Clock = fromIconly(IconlyTimeCircle, "Clock");
export const Timer = fromIconly(IconlyTimeSquare, "Timer");
export const Calendar = fromIconly(IconlyCalendar, "Calendar");
export const CalendarCheck = fromIconly(IconlyCalendar, "CalendarCheck");
export const CalendarClock = fromIconly(IconlyCalendar, "CalendarClock");

/* Actions */
export const Plus = fromIconly(IconlyPlus, "Plus");
export const Trash2 = fromIconly(IconlyDelete, "Trash2");
export const Download = fromIconly(IconlyDownload, "Download");
export const Upload = fromIconly(IconlyUpload, "Upload");
export const UploadCloud = fromIconly(IconlyUpload, "UploadCloud");
export const Play = fromIconly(IconlyPlay, "Play");
export const Filter = fromIconly(IconlyFilter2, "Filter");
export const SlidersHorizontal = fromIconly(IconlyFilter, "SlidersHorizontal");
export const ScanSearch = fromIconly(IconlyScan, "ScanSearch");

/* Objects and media */
export const FileText = fromIconly(IconlyDocument, "FileText");
export const Image = fromIconly(IconlyImage, "Image");
export const Camera = fromIconly(IconlyCamera, "Camera");
export const Star = fromIconly(IconlyStar, "Star");
export const Heart = fromIconly(IconlyHeart, "Heart");
export const MapPin = fromIconly(IconlyLocation, "MapPin");

/* Commerce */
export const ShoppingCart = fromIconly(IconlyBuy, "ShoppingCart");
export const ShoppingBag = fromIconly(IconlyBag, "ShoppingBag");
export const CreditCard = fromIconly(IconlyWallet, "CreditCard");

/* Measurement */
export const Activity = fromIconly(IconlyActivity, "Activity");
export const BarChart2 = fromIconly(IconlyChart, "BarChart2");
export const BarChart3 = fromIconly(IconlyChart, "BarChart3");

/* ---------------------------------------------------------------- lucide -- */
/* Domain, status and data glyphs Iconly's free set has no answer for. */

export {
  AlertCircle,
  AlertOctagon,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Award,
  Banknote,
  BookOpen,
  Boxes,
  Building,
  Building2,
  Check,
  CheckCircle,
  CheckCircle2,
  Circle,
  CircleAlert,
  CircleDashed,
  CircleDollarSign,
  CircleDot,
  CloudRain,
  CloudSun,
  Code,
  Copy,
  Cpu,
  Database,
  DollarSign,
  DropletIcon,
  ExternalLink,
  FileCheck2,
  FileSpreadsheet,
  Flame,
  FlaskConical,
  Gauge,
  GitBranch,
  Globe,
  Info,
  Layers,
  LineChart,
  Link2,
  List,
  Loader2,
  Megaphone,
  Menu,
  Minus,
  Moon,
  Package,
  PackageCheck,
  Pill,
  Plug,
  PlugZap,
  Radio,
  Receipt,
  RefreshCw,
  RotateCcw,
  Save,
  Scale,
  Server,
  ShipIcon,
  Shirt,
  Sparkles,
  Sprout,
  Stethoscope,
  Sun,
  Tag,
  Target,
  Terminal,
  Thermometer,
  TrendingDown,
  TrendingUp,
  Truck,
  Unlink,
  Warehouse,
  Webhook,
  Wheat,
  Wind,
  Workflow,
  Wrench,
  X,
  XCircle,
  Zap,
} from "lucide-react";
