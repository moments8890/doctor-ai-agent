/**
 * ActionFooter — bottom action bar with safe-area padding.
 *
 * Usage:
 *   <ActionFooter>
 *     <Button block color="primary">保存</Button>
 *   </ActionFooter>
 *
 *   <ActionFooter>
 *     <Button fill="outline" block>取消</Button>
 *     <Button color="primary" block>确认</Button>
 *   </ActionFooter>
 */
import { bottomBar } from "../layouts";

export default function ActionFooter({ children, style }) {
  return (
    <div
      style={{
        ...bottomBar,
        display: "flex",
        gap: 8,
        ...style,
      }}
    >
      {children}
    </div>
  );
}
