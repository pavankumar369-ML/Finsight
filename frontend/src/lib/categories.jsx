import { UtensilsCrossed, ShoppingBasket, Bus, ShoppingBag, ReceiptText, Clapperboard, HeartPulse,
  GraduationCap, House, ArrowLeftRight, Shapes, Briefcase, Laptop, Undo2, Wallet } from "lucide-react";

export const CATEGORY = {
  Food: { color: "#FF9F6B", icon: UtensilsCrossed },
  Groceries: { color: "#7BD88F", icon: ShoppingBasket },
  Transport: { color: "#74A9FF", icon: Bus },
  Shopping: { color: "#E58CF2", icon: ShoppingBag },
  Bills: { color: "#F2B53A", icon: ReceiptText },
  Entertainment: { color: "#AE93FF", icon: Clapperboard },
  Health: { color: "#5FD4D4", icon: HeartPulse },
  Education: { color: "#9DB4FF", icon: GraduationCap },
  Rent: { color: "#FF7A8A", icon: House },
  Transfers: { color: "#B8C0D9", icon: ArrowLeftRight },
  Others: { color: "#8F97B2", icon: Shapes },
  Salary: { color: "#3FD9A0", icon: Briefcase },
  Freelance: { color: "#3FD9A0", icon: Laptop },
  Refund: { color: "#3FD9A0", icon: Undo2 },
  "Other income": { color: "#3FD9A0", icon: Wallet },
};
export const EXPENSE = ["Food", "Groceries", "Transport", "Shopping", "Bills", "Entertainment", "Health", "Education", "Rent", "Transfers", "Others"];
export const INCOME = ["Salary", "Freelance", "Refund", "Other income"];
export const catMeta = (c) => CATEGORY[c] ?? CATEGORY.Others;

export function CategoryIcon({ category, size = 36 }) {
  const { color, icon: Icon } = catMeta(category);
  return (
    <span className="grid shrink-0 place-items-center rounded-[11px]"
      style={{ width: size, height: size, background: `${color}1F`, color }}>
      <Icon size={size * 0.46} strokeWidth={2} />
    </span>
  );
}
