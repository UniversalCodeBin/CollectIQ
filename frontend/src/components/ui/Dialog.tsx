import { Modal, type ModalProps } from "./Modal";

/** Mark the cancel control with data-cancel; a destructive dialog starts focus there. */
export function Dialog(props: ModalProps) {
  return <Modal placement="centre" {...props} />;
}
