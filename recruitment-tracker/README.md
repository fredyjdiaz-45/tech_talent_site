# Recruitment Tracker (Power Apps, M365 standard license, GCC)

This app tracks about 60 recruitment actions a year. Each one runs from **Intent to Recruit**, through approval (**Supervisor → Budget → IG**), the announcement and the certificates, and ends in **Filled**, **Cancelled** or a **Re-recruit**. It holds no candidate data.

| Piece | What it is |
|---|---|
| SharePoint list `Recruitment Actions` | All the data. Item attachments are where documents are stored. |
| Canvas app `Recruitment Tracker` | Generated from the list, then customized (step 3). |
| Flow `RecruitmentApproval` | The sequential 3-step approval (step 4). |

Everything uses standard connectors (SharePoint, Approvals, Office 365 Outlook). You don't need a premium license, and all of them are available in GCC.

## Decisions and assumptions

- **Funding** is two checkboxes: *Permanent Funds* and *Surge Funds*. Check both if a position is split-funded.
- **Appointment** is *Permanent* or *Term*. A term appointment also asks for an NTE date.
- **Attrition**: set *Reason* to *Backfill (Attrition)*, then fill in the departing employee and the departure date.
- **Re-recruit** creates a new record that links back through *Original Action ID*. The new record starts at **Approved** and carries over the original approval. If you want it to go through approval again, change `"Approved"` to `"Draft"` in the re-recruit button formula.
- **Documents** are stored as list item attachments. This is built in and needs no flow. The limit is that documents have no metadata of their own. If you later need document types or a retention policy, move them to a document library. Don't upload anything containing full SSNs.
- **Access**: anyone with edit rights on the list can change the Status directly in SharePoint. Version history records who made each change. Put the list on a site that only HR, hiring managers and approvers can reach.
- The **Office** choices are placeholders. Edit them in List settings → Office.

## 1. Create the list

1. Use a SharePoint site with restricted membership, such as the HR site.
2. If you have no PnP app registration yet, have IT run this once (it needs admin consent). The permissions are delegated, so the app can never do more than the person signed in. IT can trim them to SharePoint `AllSites.Manage`.
   ```powershell
   Install-Module PnP.PowerShell -Scope CurrentUser
   Register-PnPEntraIDAppForInteractiveLogin -ApplicationName "PnP Recruitment Setup" -Tenant youroig.onmicrosoft.com
   ```
3. Run the script below. It should end with `OK: 'Recruitment Actions' has all 34 columns.`
   ```powershell
   ./provision.ps1 -SiteUrl https://youroig.sharepoint.com/sites/HR -ClientId <app id from step 2>
   ```
   If IT won't allow PowerShell, create the same columns by hand from the table in [`provision.ps1`](provision.ps1). It takes about 20 minutes. Make the date columns *Date only*, rename *Title* to *Position Title*, and set it to not required.

The script also turns on versioning, which gives you the audit trail.

## 2. Generate the app

1. Open the list in SharePoint and choose **Integrate → Power Apps → Create an app**. Name it *Recruitment Tracker*. Build it in the **default environment**, because Approvals needs that environment.
2. This creates `BrowseScreen1`, `DetailScreen1` and `EditScreen1`. If your control names differ, substitute them in the formulas below.
3. On both `EditForm1` and `DetailForm1`, go to **Edit fields → Add field**, add every field, and order them to match the script's table.
4. Go to **Settings → General → Data row limit** and set it to **2000**.
5. In the **Data** pane, add the **Office 365 Outlook** connector.

## 3. Customize the app

### BrowseScreen1

Insert a **Dropdown** named `ddView` and set `Items` to `["Open", "Mine", "Pending approval", "Closed", "All"]`.

Set `BrowseGallery1.Items`:
```
// ponytail: these filters aren't delegable to SharePoint, so they only see the first 2000 rows
// (the data row limit). At ~60 a year that's ~30 years. Archive old rows to a second list before then.
Sort(
    Filter(
        'Recruitment Actions',
        TextSearchBox1.Text in Title,
        Switch(
            ddView.Selected.Value,
            "Open", !(Status.Value in ["Filled", "Cancelled", "Re-recruit"]),
            "Mine", User().Email in ['HR Specialist'.Email, 'Hiring Manager'.Email, Supervisor.Email, 'Created By'.Email],
            "Pending approval", Status.Value = "Pending Approval",
            "Closed", Status.Value in ["Filled", "Cancelled", "Re-recruit"],
            true
        )
    ),
    Modified,
    SortOrder.Descending
)
```

Set the gallery's labels:
- Title: `"#" & ThisItem.ID & "  " & ThisItem.Title`
- Subtitle: `ThisItem.Status.Value & " · " & ThisItem.Grade & " · " & ThisItem.'Duty Location'`
- Body: `"HR: " & ThisItem.'HR Specialist'.DisplayName & " · " & DateDiff(ThisItem.Created, Today()) & " days"`

Insert a **Label** above the gallery for the headline numbers:
```
"Open: " & CountIf('Recruitment Actions', !(Status.Value in ["Filled", "Cancelled", "Re-recruit"])) &
"  ·  Pending approval: " & CountIf('Recruitment Actions', Status.Value = "Pending Approval") &
"  ·  Hired: " & Sum('Recruitment Actions', 'Positions Filled') & " / 50"
```

### EditScreen1

Card settings. Select the card, then set the property:

| Cards | Property |
|---|---|
| Position Title, Series, Grade, Office, Duty Location, Recruitment Type, Appointment Type, Reason, Supervisor | `Required` = `true` |
| Date Submitted, Date Approved, Approval History, Original Action ID | `DisplayMode` = `DisplayMode.View` |
| Status | `DisplayMode` = `If(EditForm1.Mode = FormMode.New \|\| Coalesce(ThisItem.Status.Value, "Draft") in ["Draft", "Pending Approval"], DisplayMode.View, DisplayMode.Edit)` |
| Term NTE Date | `Visible` = `<Appointment Type combo box>.Selected.Value = "Term"` |
| Departing Employee, Departure Date | `Visible` = `<Reason combo box>.Selected.Value = "Backfill (Attrition)"` |

The Status lock means only the approval flow can move an action out of Draft or Pending Approval. After that, HR moves it through the stages.

**Checkboxes for funding.** In the *Permanent Funds* and *Surge Funds* cards, delete the toggle and insert a **Check box**. Set its `Default` to `Parent.Default` and its `Text` to "Permanent funds (annual appropriation)" or "Surge funds". Then set the card's `Update` to `<checkbox>.Value`.

**Attachments** are already on the form. `MaxAttachmentSize` defaults to 10 MB and can go up to 50.

**Assignment emails.** Set `EditScreen1.OnVisible`:
```
Set(varPrevHR, If(EditForm1.Mode = FormMode.Edit, BrowseGallery1.Selected.'HR Specialist'.Email));
Set(varPrevHM, If(EditForm1.Mode = FormMode.Edit, BrowseGallery1.Selected.'Hiring Manager'.Email))
```
Then set `EditForm1.OnSuccess`:
```
With({r: EditForm1.LastSubmit},
    If(!IsBlank(r.'HR Specialist'.Email) && r.'HR Specialist'.Email <> varPrevHR,
        Office365Outlook.SendEmailV2(r.'HR Specialist'.Email, "Assigned: recruitment #" & r.ID & " – " & r.Title,
            "You are the HR Specialist on this recruitment action. Open the Recruitment Tracker app for details."));
    If(!IsBlank(r.'Hiring Manager'.Email) && r.'Hiring Manager'.Email <> varPrevHM,
        Office365Outlook.SendEmailV2(r.'Hiring Manager'.Email, "Assigned: recruitment #" & r.ID & " – " & r.Title,
            "You are the Hiring Manager on this recruitment action. Open the Recruitment Tracker app for details."))
);
Back()
```
Emails go out only when someone is newly assigned through the app. Assignments edited directly in SharePoint don't send an email.

### DetailScreen1

Build the flow in step 4 first, so that `RecruitmentApproval` exists. Then add two buttons.

**Submit for approval**
- `Visible`: `Coalesce(BrowseGallery1.Selected.Status.Value, "Draft") = "Draft"`
- `DisplayMode`: `If(BrowseGallery1.Selected.'Permanent Funds' || BrowseGallery1.Selected.'Surge Funds', DisplayMode.Edit, DisplayMode.Disabled)`
- `Text`: `If(Self.DisplayMode = DisplayMode.Edit, "Submit for approval", "Check a funding source first")`
- `OnSelect`:
```
IfError(
    RecruitmentApproval.Run(BrowseGallery1.Selected.ID),
    Notify("Approval did not start: " & FirstError.Message, NotificationType.Error),
    Patch('Recruitment Actions', BrowseGallery1.Selected, {Status: {Value: "Pending Approval"}, 'Date Submitted': Today()});
    Notify("Sent to supervisor for approval.", NotificationType.Success)
)
```

**Create re-recruit**
- `Visible`: `BrowseGallery1.Selected.Status.Value = "Re-recruit"`
- `DisplayMode` (this prevents creating a duplicate): `If(IsBlank(LookUp('Recruitment Actions', 'Original Action ID' = BrowseGallery1.Selected.ID)), DisplayMode.Edit, DisplayMode.Disabled)`
- `OnSelect`:
```
With({o: BrowseGallery1.Selected},
    Set(varNew, Patch('Recruitment Actions', Defaults('Recruitment Actions'), {
        Title: o.Title, Series: o.Series, Grade: o.Grade, Office: o.Office, 'Duty Location': o.'Duty Location',
        'Number of Vacancies': Max(1, o.'Number of Vacancies' - o.'Positions Filled'),
        'Recruitment Type': o.'Recruitment Type', 'Appointment Type': o.'Appointment Type', 'Term NTE Date': o.'Term NTE Date',
        'Permanent Funds': o.'Permanent Funds', 'Surge Funds': o.'Surge Funds',
        Reason: o.Reason, 'Departing Employee': o.'Departing Employee', 'Departure Date': o.'Departure Date',
        Justification: o.Justification, Supervisor: o.Supervisor,
        'HR Specialist': o.'HR Specialist', 'Hiring Manager': o.'Hiring Manager',
        Status: {Value: "Approved"}, 'Date Submitted': o.'Date Submitted', 'Date Approved': o.'Date Approved',
        'Original Action ID': o.ID,
        'Approval History': "Re-recruit of #" & o.ID & " (original approval carried over)." & Char(10) & o.'Approval History'
    }))
);
Notify("Created re-recruit #" & varNew.ID, NotificationType.Success)
```

## 4. Approval flow `RecruitmentApproval`

In Power Apps Studio, open the **Power Automate** pane and choose **Create new flow → Create from blank**. That adds the trigger below and connects the flow to the app.

1. **When Power Apps calls a flow (V2)**: add a **Number** input named `ItemID`.
2. **SharePoint – Get item**: pick your site, list *Recruitment Actions*, and set Id to `ItemID`.
3. **Initialize variable** `Rejected`: Boolean, `false`.
4. **Initialize variable** `History`: String, with the expression `coalesce(body('Get_item')?['ApprovalHistory'], '')`.
5. **Compose**, renamed `Approvers`. Use your real Budget and IG emails. For several people, separate them with `;`, and the first to respond decides.
   ```
   [
     {"Step": "Supervisor", "Email": "<dynamic content: Supervisor Email>"},
     {"Step": "Budget",     "Email": "budget.officer@youroig.gov"},
     {"Step": "IG",         "Email": "ig@youroig.gov"}
   ]
   ```
6. **Apply to each** (called *For each* in the new designer) over `outputs('Approvers')`. Leave concurrency off so the steps run in order. Inside it:
   - **Condition** `variables('Rejected')` is equal to `false`. In the **True** branch:
     - **Start and wait for an approval**, type *Approve/Reject – First to respond*.
       - Title: `@{item()?['Step']} approval – Intent to Recruit #@{ItemID}: @{Title}`
       - Assigned to: `@{item()?['Email']}`
       - Item link: *Link to item*
       - Details:
         ```
         - **Position:** {Title}, {Series}, {Grade}
         - **Office / location:** {Office Value} / {Duty Location}
         - **Vacancies:** {Number of Vacancies}
         - **Recruitment type:** {Recruitment Type Value}
         - **Appointment:** {Appointment Type Value} {Term NTE Date}
         - **Funding:** @{if(body('Get_item')?['FundPermanent'], 'Permanent ', '')}@{if(body('Get_item')?['FundSurge'], 'Surge', '')}
         - **Reason:** {Reason Value} {Departing Employee}
         - **Justification:** {Justification}
         ```
     - **Append to string variable** `History`, ending with a line break:
       `@{convertFromUtc(utcNow(), 'Eastern Standard Time', 'yyyy-MM-dd')} @{item()?['Step']}: @{body('Start_and_wait_for_an_approval')?['outcome']} by @{body('Start_and_wait_for_an_approval')?['responses'][0]?['responder']?['displayName']} – @{body('Start_and_wait_for_an_approval')?['responses'][0]?['comments']}`
     - **SharePoint – Update item**: Id = `ItemID`, Approval History = `History`. This lets the app show which step the action has reached.
     - **Condition**: if `body('Start_and_wait_for_an_approval')?['outcome']` is equal to `Reject`, then **Set variable** `Rejected` = `true`.
7. After the loop, add a **Condition** checking that `variables('Rejected')` is equal to `true`.
   - **True**: **Update item** with Status = *Draft*. Then **Send an email (V2)** to *Created By Email*, with the subject "Returned: Intent to Recruit #ItemID" and the body `History`.
   - **False**: **Update item** with Status = *Approved* and Date Approved = `convertFromUtc(utcNow(), 'Eastern Standard Time', 'yyyy-MM-dd')`. Then **Send an email (V2)** to *Created By Email*, with the subject "Approved: Intent to Recruit #ItemID" and the body `History`.

If your office isn't on Eastern time, change the time zone. The expressions assume the default action names (`Get_item`, `Start_and_wait_for_an_approval`). The first run of Approvals can take a few minutes while it sets itself up.

## 5. Smoke test

Run through this once before go-live:

1. `provision.ps1` ends with `OK: ... all 34 columns`.
2. Create a new action and leave both funding boxes unchecked. The Submit button should be disabled.
3. Check *Surge*, then submit. The status should change to *Pending Approval*, and the supervisor should get an approval request.
4. Approve as the supervisor. A history line should appear and Budget should get the request. Reject as Budget. The status should go back to *Draft*, the requester should get an email, and the IG should never be asked.
5. Resubmit and approve all three steps. The status should be *Approved* with Date Approved set, and Status should now be editable.
6. Assign an HR Specialist. That person should get an email. Save again without changing it, and no second email should go out.
7. Set the status to *Re-recruit* with Positions Filled = 0, then choose **Create re-recruit**. A new action should appear at *Approved*, linked back to the original, and the button should now be disabled.
8. Attach a PDF. It should show on the detail screen and on the SharePoint item.

For ad-hoc reporting, use **Export to Excel** on the list. Add Power BI only if the headline label and the list views stop being enough.
