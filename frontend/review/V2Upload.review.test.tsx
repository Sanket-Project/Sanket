import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ImportUploader } from "@/components/integrations/ImportUploader";
import { useAuthStore } from "@/stores/auth";

const api=vi.hoisted(()=>({analyze:vi.fn(),upload:vi.fn(),v2Preview:vi.fn(),v2Confirm:vi.fn()}));
vi.mock("@/api/integrations",()=>({integrationsApi:api}));
vi.mock("react-hot-toast",()=>({default:{success:vi.fn(),error:vi.fn()}}));

it("confirms a valid V2 preview when the user presses Import",async()=>{
  useAuthStore.setState({tenantId:"review-tenant",userId:"review-user",role:"admin"});
  api.v2Preview.mockResolvedValue({schema:"retail_v2.0.sales",row_count:1,headers:[],errors:[],can_confirm:true,preview_token:"review-token"});
  api.v2Confirm.mockResolvedValue({rows:1,inserted:1,skipped:0});
  const source="schema_version\nretail_v2.0.sales\n";
  const file=new File([source],"sales.csv",{type:"text/csv"});
  Object.defineProperty(file,"slice",{value:()=>({text:async()=>source})});
  const user=userEvent.setup();
  const {container}=render(<ImportUploader kind="sales" />);
  await user.upload(container.querySelector('input[type="file"]')!,file);
  await screen.findByLabelText("V2 preview");
  const button=screen.getByRole("button",{name:"Import"});
  expect(button).toBeEnabled();
  await user.click(button);
  await waitFor(()=>expect(api.v2Confirm).toHaveBeenCalledWith(file,"review-token"));
});
