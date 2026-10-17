# Privacy of public Dinext repositories

This policy covers public repositories in Dinext-pro. Preserve inherited upstream code, data, authors and licenses. Review only our additions in external forks. The private Docs and Control Center repositories are excluded from anonymization.

Configure the author separately in each new public working copy:

```sh
git config --local user.name Administrator
git config --local user.email administrator@dinext.invalid
```

Use `Administrator` for exported `owner`, `modified_by` and references to the built-in Frappe administrator. Use `administrator@dinext.invalid` where a synthetic email is required. Keep references valid: an email placeholder does not create a User record. Examples may use reserved `.invalid`, `.example` and `.test` domains.

Export application definitions and configuration. Exclude real User, Employee, Contact, Customer records, customer documents, production database dumps and credentials. Review attached spreadsheets, documents, images and their metadata before publication. New binary attachments require a private content review before their checksum is added to the shared approved-assets file. Keep real service accounts and required upstream attribution valid.

The shared CI guard checks new commits and added content, preserves verified vendor ancestry and reports safe locations without printing the detected values. The identifier dictionary is held in an encrypted Actions secret and is read only by the guard. Application tests do not receive it.

GitHub can add account identities when it creates merge commits. Maintainers must review these under the same policy. Rewriting Git does not rename GitHub accounts, PR authors or Actions actors; old PR references and cached objects may require GitHub Support.

The public history was replaced on 17 October 2026. Create a fresh clone before resuming work. Preserve unfinished changes privately and reapply them as a reviewed patch onto clean history. Do not merge or force-push an old clone back into a public repository. Keep recovery originals and identifier mappings private.
