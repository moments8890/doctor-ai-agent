/**
 * NewItemCard — "+" card for creating new items.
 * Used at the top of patient list, task list, record list, etc.
 */
import { COLOR } from "../theme";
import ListCard from "./ListCard";
import IconBadge from "./IconBadge";
import { ICON_BADGES } from "../pages/doctor/constants";

export default function NewItemCard({ title, subtitle, onClick }) {
  return (
    <ListCard
      avatar={<IconBadge config={ICON_BADGES.kb_add} />}
      title={title}
      subtitle={subtitle}
      onClick={onClick}
      sx={{ "& .MuiTypography-root:first-of-type": { color: COLOR.success } }}
    />
  );
}
