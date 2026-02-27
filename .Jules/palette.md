## 2024-05-24 - Input Component Accessibility
**Learning:** Automatically linking error messages to inputs using `aria-describedby` and `useId` significantly improves the screen reader experience for form validation. Explicitly setting `aria-invalid` provides immediate feedback.
**Action:** Always use `useId` for generating unique IDs for helper text and error messages in form components to ensure robust accessibility without requiring manual ID management from the consumer.
