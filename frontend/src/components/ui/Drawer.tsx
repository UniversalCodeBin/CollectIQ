import { Modal, type ModalProps } from "./Modal";

export function Drawer(props: ModalProps) {
  return <Modal placement="side" {...props} />;
}
