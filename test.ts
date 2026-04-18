import { IMessageSDK } from '@photon-ai/imessage-kit'

const sdk = new IMessageSDK({ debug: true })

// Test 1: Send a message to yourself
await sdk.send('+19165448193', 'Hannah is amazing!')

// Test 2: Read your unread messages
const unread = await sdk.getUnreadMessages()
for (const { sender, messages } of unread.groups) {
  console.log(`${sender}: ${messages.length} unread messages`)
}

await sdk.close()


