/**
 * Buying a pack of reports with Razorpay Checkout (UPI, cards, net banking).
 *
 * The server makes the order and decides the price. Razorpay's window takes the payment and
 * hands back a signature, which the server checks before any report is added: nothing the
 * page says on its own can add reports.
 */
import { payOrder, payVerify } from "./api"
import type { Me } from "./types"

interface RazorpayResult {
  razorpay_order_id: string
  razorpay_payment_id: string
  razorpay_signature: string
}

interface RazorpayOptions {
  key: string
  amount: number
  currency: string
  name: string
  description: string
  order_id: string
  handler: (result: RazorpayResult) => void
  modal: { ondismiss: () => void }
  theme: { color: string }
}

declare global {
  interface Window {
    Razorpay?: new (options: RazorpayOptions) => { open: () => void }
  }
}

let loading: Promise<void> | null = null
function loadCheckout(): Promise<void> {
  if (window.Razorpay) return Promise.resolve()
  loading ??= new Promise((resolve, reject) => {
    const s = document.createElement("script")
    s.src = "https://checkout.razorpay.com/v1/checkout.js"
    s.async = true
    s.onload = () => resolve()
    s.onerror = () => {
      loading = null
      reject(new Error("The payment window couldn't load. Check your connection or ad blocker and try again."))
    }
    document.head.appendChild(s)
  })
  return loading
}

/** Opens the payment window. Resolves with the account once paid, or null if it was closed. */
export async function buyPack(packId: string): Promise<Me | null> {
  const order = await payOrder(packId)
  await loadCheckout()
  return new Promise((resolve, reject) => {
    const checkout = new window.Razorpay!({
      key: order.key_id,
      amount: order.amount,
      currency: order.currency,
      name: "LabForge",
      description: `${order.reports} lab reports`,
      order_id: order.order_id,
      handler: (result) => {
        payVerify({
          order_id: result.razorpay_order_id,
          payment_id: result.razorpay_payment_id,
          signature: result.razorpay_signature,
        }).then(resolve, reject)
      },
      modal: { ondismiss: () => resolve(null) },
      theme: { color: "#1d3fc4" },
    })
    checkout.open()
  })
}
