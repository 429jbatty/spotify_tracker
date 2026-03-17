import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

function AlbumCredits({ groupedCredits }) {
  const hasCredits = Object.values(groupedCredits).some(
    (group) => Object.keys(group).length > 0
  );

  if (!hasCredits) return null;

  return (
    <div className="border-t border-border pt-4">
      <Accordion type="single" collapsible className="w-full">
        <AccordionItem value="credits" className="border-0">
          <AccordionTrigger className="hover:no-underline py-2 px-0 font-semibold text-foreground">
            Credits
          </AccordionTrigger>

          <AccordionContent className="space-y-4 pb-0">
            {Object.entries(groupedCredits).map(([groupName, persons]) => {
              if (Object.keys(persons).length === 0) return null;

              return (
                <div key={groupName} className="space-y-2">
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-foreground/70">
                    {groupName}
                  </h4>

                  <div className="space-y-1 ml-2">
                    {Object.entries(persons).map(([name, roles]) => (
                      <div key={name} className="text-xs text-foreground/70">
                        <span className="font-medium">{name}</span>
                        <span className="text-foreground/50">
                          {" "}— {roles.join(", ")}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  );
}

export default AlbumCredits;