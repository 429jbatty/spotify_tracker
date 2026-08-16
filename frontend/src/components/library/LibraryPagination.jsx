import { Button } from "@/components/ui/button";

export const LIBRARY_PAGE_SIZE = 50;

function LibraryPagination({ page, totalItems, onPageChange }) {
  const pageCount = Math.ceil(totalItems / LIBRARY_PAGE_SIZE);

  if (pageCount <= 1) return null;

  const firstItem = page * LIBRARY_PAGE_SIZE + 1;
  const lastItem = Math.min((page + 1) * LIBRARY_PAGE_SIZE, totalItems);

  return (
    <nav className="mt-4 flex flex-wrap items-center justify-between gap-3" aria-label="Library pagination">
      <p className="text-sm text-muted-foreground">
        Showing {firstItem}–{lastItem} of {totalItems} albums
      </p>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          disabled={page === 0}
          onClick={() => onPageChange(page - 1)}
        >
          Previous
        </Button>
        <span className="text-sm text-muted-foreground">Page {page + 1} of {pageCount}</span>
        <Button
          type="button"
          variant="outline"
          disabled={page === pageCount - 1}
          onClick={() => onPageChange(page + 1)}
        >
          Next
        </Button>
      </div>
    </nav>
  );
}

export default LibraryPagination;
