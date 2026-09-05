#ifndef USB_PROTO_H
#define USB_PROTO_H

/* A appeler regulierement : draine l'USB CDC et met a jour l'UI.
   Non bloquant. */
void usb_proto_poll(void);

#endif /* USB_PROTO_H */
