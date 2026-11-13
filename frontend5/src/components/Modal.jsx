function Modal({ title, onClose, children, wide }) {
  return (
    <div className="modal-scrim" onClick={onClose}>
      <div
        className={`modal-card ${wide ? "modal-wide" : ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2>{title}</h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export default Modal;
