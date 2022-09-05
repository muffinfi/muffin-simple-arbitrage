### Build

```bash
forge build --root .
```

### Deploy

```bash
forge create Arbitrageur4 \
    --root . \
    --rpc-url=$RPC_URL \
    --private-key=$PRIVATE_KEY \
    --constructor-args "$HUB_ADDRESS" "$WETH_ADDRESS" "$OWNER_ADDRESS" "$EXECUTOR_ADDRESS"
```
